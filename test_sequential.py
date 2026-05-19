"""Test all three templates sequentially with rate-limit-aware delays."""
import base64, json, os, re, sys, time, urllib.request

SITE = "https://ncformatter.vercel.app"

def call_api(endpoint, payload):
    url = f"{SITE}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body[:400]}")
        return None

def test_template(name, docx_path, expected_path, checks_fn):
    print(f"\n{'='*60}")
    print(f"Testing {name}")
    print(f"{'='*60}")
    
    if not os.path.exists(docx_path):
        print(f"  SKIP: {docx_path} not found")
        return None
    
    with open(docx_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    
    print(f"  Step 1: process-doc...")
    r1 = call_api("/api/process-doc", {"fileData": b64, "fileName": os.path.basename(docx_path)})
    if not r1 or not r1.get("success"):
        print(f"  FAIL: process-doc: {r1}")
        return False
    
    ir = r1["ir"]
    print(f"  IR: {len(ir.get('blocks', []))} blocks")
    
    print(f"  Step 2: generate-template...")
    r2 = call_api("/api/generate-template", {"ir": ir, "docMeta": {}})
    if not r2 or not r2.get("success"):
        print(f"  FAIL: generate-template failed")
        return False
    
    html = r2.get("html", "").strip()
    outpath = f"{name.lower()}_live_output.html"
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Output saved ({len(html)} chars)")
    
    with open(expected_path, "r", encoding="utf-8") as f:
        expected = f.read().strip()
    
    return checks_fn(html, expected)

def checks_lm300(html, expected):
    issues = []
    lines = html.split("\n")
    
    if not any("Property Address:" in l for l in lines):
        issues.append("Missing 'Property Address:' label")
    if "M583" in html:
        issues.append("M583 found (should NOT be present)")
    if "margin-left:" not in html:
        issues.append("Bullet table missing margin-left")
    
    sincerely_idx = next((i for i, l in enumerate(lines) if "Sincerely," in l), None)
    if sincerely_idx is not None:
        nxt = [l.strip() for l in lines[sincerely_idx+1:sincerely_idx+3] if l.strip()]
        if nxt and nxt[0] == "<br>":
            issues.append("Extra <br> after Sincerely")
    
    compress_match = re.search(r'Compress\(([^)]+M567[^)]+)\)', html)
    if compress_match:
        parts = compress_match.group(1).split("|")
        if len([p for p in parts if p.strip()]) != 2:
            issues.append(f"Compress should have 2 parts, has {len(parts)}")
    
    for issue in issues:
        print(f"  FAIL: {issue}")
    if not issues:
        print(f"  ALL CHECKS PASSED!")
    return len(issues) == 0

def checks_ia004(html, expected):
    issues = []
    
    if "M583" not in html:
        issues.append("M583 missing (should have 3-part Compress)")
    else:
        print("  PASS: M583 present")
    
    if 'colspan="2"' not in html:
        issues.append("Missing colspan=2 for loan number row")
    else:
        print("  PASS: colspan=2")
    
    if 'border: 1px solid' not in html and 'border:1px solid' not in html:
        issues.append("Missing bordered comparison table")
    else:
        print("  PASS: Bordered table")
    
    if re.search(r'<td[^>]*>RE:</td>', html):
        print("  PASS: RE label present")
    else:
        issues.append("Missing RE: label")
    
    if '{[tagHeader]}' in html:
        print("  PASS: {[tagHeader]}")
    else:
        issues.append("Wrong header format")
    
    if 'Math(' in html:
        print("  PASS: Math() present")
    else:
        issues.append("Missing Math() function")
    
    if 'FHA Resource Center' in html:
        print("  PASS: FHA Resource Center")
    else:
        issues.append("Missing FHA Resource Center")
    
    for issue in issues:
        print(f"  FAIL: {issue}")
    if not issues:
        print(f"  ALL CHECKS PASSED!")
    return len(issues) == 0

def checks_cl008(html, expected):
    issues = []
    
    if "M583" not in html:
        issues.append("M583 missing (should have 3-part Compress)")
    else:
        print("  PASS: M583 present")
    
    if 'width="3%"' in html:
        print("  PASS: 3-column RE table")
    else:
        issues.append("Missing 3-column RE table")
    
    if "margin-left:" in html:
        print("  PASS: Bullet lists have margin-left")
    else:
        issues.append("Bullet lists missing margin-left")
    
    if 'valign="top">1.</td>' in html:
        print("  PASS: Numbered list items")
    else:
        issues.append("Missing numbered list items")
    
    if "Property Address:" in html:
        print("  PASS: Property Address label")
    else:
        issues.append("Missing Property Address label")
    
    if "&amp;" in html:
        print("  PASS: Ampersand encoding")
    else:
        issues.append("Missing &amp; encoding")
    
    for issue in issues:
        print(f"  FAIL: {issue}")
    if not issues:
        print(f"  ALL CHECKS PASSED!")
    return len(issues) == 0

if __name__ == "__main__":
    tests = [
        ("LM300", r"C:\Users\jhamrick\Downloads\LM300_VP_HUD Pre-Foreclosure Sale_V1 (1).docx",
         r"formatter examples\LM300\LM300-formatted.html", checks_lm300),
        ("IA004", r"C:\Users\jhamrick\Downloads\IA004 - FHA Coverage Term - FUB - V1.0 (1).docx",
         r"formatter examples\IA004\IA004-formatted.html", checks_ia004),
        ("CL008", r"C:\Users\jhamrick\Downloads\CL008 - Loss Mit Consult 44 Day - Commerce - V1.0 (2).docx",
         r"formatter examples\CL008\CL008-formatted.html", checks_cl008),
    ]
    
    results = {}
    for i, (name, docx, exp, fn) in enumerate(tests):
        if i > 0:
            print(f"\n  Waiting 90s for rate limit...")
            time.sleep(90)
        result = test_template(name, docx, exp, fn)
        results[name] = result
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else ("SKIP" if passed is None else "FAIL")
        print(f"  {name}: {status}")
        if not passed:
            all_pass = False
    
    if all_pass:
        print("\nALL TEMPLATES PASS!")
    sys.exit(0 if all_pass else 1)
