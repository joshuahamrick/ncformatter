"""Inspect LM300 IR to see what labels/variables Claude receives."""
import base64
import json
import urllib.request

SITE = "https://ncformatter.vercel.app"
DOCX = r"C:\Users\jhamrick\Downloads\LM300_VP_HUD Pre-Foreclosure Sale_V1 (1).docx"

with open(DOCX, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

data = json.dumps({"fileData": b64, "fileName": "LM300.docx"}).encode("utf-8")
req = urllib.request.Request(f"{SITE}/api/process-doc", data=data, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read().decode("utf-8"))

ir = result["ir"]
blocks = ir.get("blocks", [])

print(f"Total blocks: {len(blocks)}")
print(f"\nFirst 25 blocks (looking for RE/Property Address/M583):")
for i, b in enumerate(blocks[:25]):
    if b.get("type") == "paragraph":
        runs = b.get("runs", [])
        text = "".join(r.get("text", "") for r in runs).strip()
        fmt = []
        if b.get("isListItem"):
            lt = b.get("listType", "bullet")
            fmt.append(f"LIST_ITEM(type={lt})")
        if b.get("alignment"):
            fmt.append(f"ALIGN_{b['alignment'].upper()}")
        fmt_str = f" [{', '.join(fmt)}]" if fmt else ""
        if text:
            print(f"  Block {i}: {text[:120]}{fmt_str}")
    elif b.get("type") == "table":
        print(f"  Block {i}: [TABLE with {len(b.get('rows', []))} rows]")

print(f"\n--- Searching ALL blocks for M583 ---")
for i, b in enumerate(blocks):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs)
    if "M583" in text or "583" in text:
        print(f"  Block {i}: {text[:200]}")

print(f"\n--- Searching ALL blocks for 'Property Address' ---")
for i, b in enumerate(blocks):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs)
    if "property" in text.lower() or "address" in text.lower():
        print(f"  Block {i}: {text[:200]}")

print(f"\n--- Searching ALL blocks for 'RE:' ---")
for i, b in enumerate(blocks):
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs)
    if text.strip().startswith("RE:") or "RE: Loan" in text:
        print(f"  Block {i}: {text[:200]}")
