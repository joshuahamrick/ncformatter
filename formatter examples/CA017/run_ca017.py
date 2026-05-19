import base64, json, urllib.request

SITE = "https://ncformatter.vercel.app"
DOCX = r"k:\ncConnect\Letters\Triad\Letters\CA017\20260505\CA017 - Foreclosure Ln Reinstated - Triad - V2.0 (1).docx"
OUT_DIR = r"C:\Users\jhamrick\Desktop\NcFormatter\formatter examples\CA017"

def call_api(endpoint, payload):
    url = f"{SITE}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))

with open(DOCX, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

print("Step 1: process-doc...")
r1 = call_api("/api/process-doc", {"fileData": b64, "fileName": "CA017.docx"})
if not r1.get("success"):
    print("FAIL:", r1)
    exit(1)
ir = r1["ir"]
print(f"  IR blocks: {len(ir.get('blocks', []))}")

with open(f"{OUT_DIR}\\CA017-ir.json", "w") as f:
    json.dump(ir, f, indent=2)
print("  IR saved.")

print("Step 2: generate-template...")
r2 = call_api("/api/generate-template", {"ir": ir, "docMeta": {}})
if not r2.get("success"):
    print("FAIL:", r2)
    exit(1)

html = r2["html"]
with open(f"{OUT_DIR}\\CA017-ai-output.html", "w", encoding="utf-8") as f:
    f.write(html)
print("  AI output saved.")
print()
print(html)
