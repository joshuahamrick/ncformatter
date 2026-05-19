"""Test IA004 only."""
import base64, json, os, re, urllib.request

SITE = "https://ncformatter.vercel.app"
DOCX = r"C:\Users\jhamrick\Downloads\IA004 - FHA Coverage Term - FUB - V1.0 (1).docx"
EXPECTED = r"formatter examples\IA004\IA004-formatted.html"

def call_api(endpoint, payload):
    url = f"{SITE}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body[:500]}")
        return None

with open(DOCX, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("ascii")

print("Step 1: process-doc...")
r1 = call_api("/api/process-doc", {"fileData": b64, "fileName": os.path.basename(DOCX)})
if not r1 or not r1.get("success"):
    print(f"FAIL: {r1}")
    exit(1)

ir = r1["ir"]
print(f"  IR: {len(ir.get('blocks', []))} blocks")

print("Step 2: generate-template...")
r2 = call_api("/api/generate-template", {"ir": ir, "docMeta": {}})
if not r2 or not r2.get("success"):
    print(f"FAIL: {r2}")
    exit(1)

html = r2.get("html", "").strip()
with open("ia004_live_output.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"  Output saved. Length: {len(html)}")

with open(os.path.join(os.path.dirname(__file__), EXPECTED), "r", encoding="utf-8") as f:
    expected = f.read().strip()

# IA004-specific checks
issues = []

# Check 1: M583 SHOULD be present (IA004 has 3-part address)
if "M583" in html:
    print("  PASS: M583 present (correct for IA004)")
else:
    issues.append("FAIL: M583 missing — IA004 should have 3-part Compress")

# Check 2: colspan=2 for loan number
if 'colspan="2"' in html:
    print("  PASS: colspan=2 for loan number row")
else:
    issues.append("FAIL: Missing colspan=2")

# Check 3: Bordered comparison table
if 'border: 1px solid' in html or 'border:1px solid' in html:
    print("  PASS: Bordered comparison table")
else:
    issues.append("FAIL: Missing bordered table")

# Check 4: RE label on second row
if re.search(r'<td[^>]*>RE:</td>', html):
    print("  PASS: RE label on second row")
else:
    issues.append("FAIL: Missing RE: label on second row")

# Check 5: {[tagHeader]} (IA004 uses tagHeader, not Header(NMLSID))
if '{[tagHeader]}' in html:
    print("  PASS: Uses {[tagHeader]}")
elif '{Header(NMLSID)}' in html:
    issues.append("FAIL: Uses Header(NMLSID) instead of {[tagHeader]}")
else:
    issues.append(f"FAIL: Unknown header format")

# Check 6: FHA Resource Center table
if 'FHA Resource Center' in html:
    print("  PASS: FHA Resource Center table present")
else:
    issues.append("FAIL: Missing FHA Resource Center info")

# Check 7: Math() addition for tax
if 'Math(' in html:
    print("  PASS: Math() function present")
else:
    issues.append("FAIL: Missing Math() function")

# Check 8: Sincerely with <br> after
sincerely_found = False
for i, line in enumerate(html.split("\n")):
    if "Sincerely," in line:
        sincerely_found = True
        next_lines = [l.strip() for l in html.split("\n")[i+1:i+3] if l.strip()]
        if next_lines and next_lines[0] == "<br>":
            print("  PASS: <br> after Sincerely (correct for IA004)")
        else:
            issues.append("FAIL: Missing <br> after Sincerely — IA004 should have it")
        break

if issues:
    print(f"\nISSUES ({len(issues)}):")
    for issue in issues:
        print(f"  {issue}")
else:
    print("\nIA004: ALL CHECKS PASSED!")
