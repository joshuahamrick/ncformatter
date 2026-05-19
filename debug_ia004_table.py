"""Deep inspect IA004 table Block 99."""
import base64, json, urllib.request

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

# Deep inspect all table blocks
for i, b in enumerate(blocks):
    if b.get("type") == "table":
        rows = b.get("rows", [])
        print(f"Block {i}: TABLE with {len(rows)} rows")
        for j, row in enumerate(rows):
            cells = row.get("cells", [])
            print(f"  Row {j} ({len(cells)} cells):")
            for k, cell in enumerate(cells):
                runs = cell.get("runs", [])
                text = "".join(r.get("text", "") for r in runs)
                print(f"    Cell {k}: text='{text}' runs={len(runs)}")
                for ri, run in enumerate(runs[:3]):
                    print(f"      Run {ri}: text='{run.get('text', '')}' bold={run.get('bold')} fontSizePt={run.get('fontSizePt')}")
                if len(runs) > 3:
                    print(f"      ... and {len(runs) - 3} more runs")

# Also check blocks around the table for context
print(f"\n--- Blocks 95-105 (around table) ---")
for i in range(max(0, 95), min(len(blocks), 105)):
    b = blocks[i]
    runs = b.get("runs", [])
    text = "".join(r.get("text", "") for r in runs).strip()
    btype = b.get("type", "?")
    if text:
        print(f"  Block {i} ({btype}): {text[:120]}")
    elif btype == "table":
        print(f"  Block {i} (table): {len(b.get('rows', []))} rows [shown above]")
    else:
        print(f"  Block {i} ({btype}): [empty]")
