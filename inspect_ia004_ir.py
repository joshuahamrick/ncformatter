"""Inspect IA004 IR."""
import base64, json, urllib.request, re

SITE = "https://ncformatter.vercel.app"
DOCX = r"C:\Users\jhamrick\Downloads\IA004 - FHA Coverage Term - FUB - V1.0 (1).docx"

with open(DOCX, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

data = json.dumps({"fileData": b64, "fileName": "IA004.docx"}).encode("utf-8")
req = urllib.request.Request(f"{SITE}/api/process-doc", data=data, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read().decode("utf-8"))

ir = result["ir"]
blocks = ir.get("blocks", [])
print(f"Total blocks: {len(blocks)}")

# Check for M583 and M568
print("\n--- M583 search ---")
for i, b in enumerate(blocks):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs)
    if "M583" in text or "583" in text:
        print(f"  Block {i}: {text[:150]}")

print("\n--- M568 search ---")
for i, b in enumerate(blocks):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs)
    if "M568" in text or "568" in text:
        print(f"  Block {i}: {text[:150]}")

print("\n--- M567 search ---")
for i, b in enumerate(blocks):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs)
    if "M567" in text:
        print(f"  Block {i}: {text[:150]}")

print("\n--- Table blocks ---")
for i, b in enumerate(blocks):
    if b.get("type") == "table":
        rows = b.get("rows", [])
        print(f"  Block {i}: TABLE with {len(rows)} rows")
        for j, row in enumerate(rows[:3]):
            cells = row.get("cells", [])
            cell_texts = []
            for c in cells[:5]:
                ct = "".join(r.get("text", "") for r in c.get("runs", []))
                cell_texts.append(ct[:80])
            print(f"    Row {j}: {' | '.join(cell_texts)}")

print("\n--- RE/Loan Number lines ---")
for i, b in enumerate(blocks):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs)
    if re.search(r'RE:|Loan Number|Property', text, re.IGNORECASE):
        print(f"  Block {i}: {text[:150]}")

print("\n--- All blocks (first 30) ---")
for i, b in enumerate(blocks[:30]):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs).strip()
    btype = b.get("type", "?")
    if text:
        print(f"  Block {i} ({btype}): {text[:120]}")
    elif btype == "table":
        rows = b.get("rows", [])
        print(f"  Block {i} (table): {len(rows)} rows")
