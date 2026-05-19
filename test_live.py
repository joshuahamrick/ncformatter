"""
Live test script for NcFormatter API.
Sends .docx files to the deployed API and compares output against expected HTML.
"""
import base64
import json
import sys
import os
import re
import urllib.request

SITE = "https://ncformatter.vercel.app"

TEST_CASES = [
    {
        "name": "LM300",
        "docx": r"C:\Users\jhamrick\Downloads\LM300_VP_HUD Pre-Foreclosure Sale_V1 (1).docx",
        "expected": r"formatter examples\LM300\LM300-formatted.html",
    },
    {
        "name": "IA004",
        "docx": r"C:\Users\jhamrick\Downloads\IA004 - FHA Coverage Term - FUB - V1.0 (1).docx",
        "expected": r"formatter examples\IA004\IA004-formatted.html",
    },
    {
        "name": "CL008",
        "docx": r"C:\Users\jhamrick\Downloads\CL008 - Loss Mit Consult 44 Day - Commerce - V1.0 (2).docx",
        "expected": r"formatter examples\CL008\CL008-formatted.html",
    },
]

def normalize(html):
    """Normalize HTML for comparison: strip whitespace, normalize tags."""
    html = html.strip()
    html = re.sub(r'\r\n', '\n', html)
    html = re.sub(r'[ \t]+\n', '\n', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html

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
    except Exception as e:
        print(f"  Error: {e}")
        return None

def run_test(tc):
    name = tc["name"]
    docx_path = tc["docx"]
    expected_path = os.path.join(os.path.dirname(__file__), tc["expected"])
    
    print(f"\n{'='*60}")
    print(f"Testing {name}")
    print(f"{'='*60}")
    
    if not os.path.exists(docx_path):
        print(f"  SKIP: docx not found: {docx_path}")
        return None
    if not os.path.exists(expected_path):
        print(f"  SKIP: expected HTML not found: {expected_path}")
        return None
    
    with open(expected_path, "r", encoding="utf-8") as f:
        expected_html = normalize(f.read())
    
    with open(docx_path, "rb") as f:
        file_bytes = f.read()
    b64 = base64.b64encode(file_bytes).decode("ascii")
    
    print(f"  Step 1: Calling /api/process-doc...")
    result = call_api("/api/process-doc", {"fileData": b64, "fileName": os.path.basename(docx_path)})
    if not result or not result.get("success"):
        print(f"  FAIL: process-doc failed: {result}")
        return False
    
    ir = result["ir"]
    block_count = len(ir.get("blocks", []))
    print(f"  IR extracted: {block_count} blocks")
    
    print(f"  Step 2: Calling /api/generate-template...")
    result2 = call_api("/api/generate-template", {"ir": ir, "docMeta": {}})
    if not result2 or not result2.get("success"):
        print(f"  FAIL: generate-template failed: {result2}")
        return False
    
    generated_html = normalize(result2.get("html", ""))
    
    output_path = os.path.join(os.path.dirname(__file__), f"{name.lower()}_live_output.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(generated_html)
    print(f"  Output saved to: {output_path}")
    
    checks = compare_output(name, generated_html, expected_html)
    return checks

def compare_output(name, generated, expected):
    """Compare generated HTML against expected, checking specific known issues."""
    issues = []
    gen_lines = generated.split("\n")
    exp_lines = expected.split("\n")
    
    if name == "LM300":
        # Check 1: Property Address label (should be "Property Address:" not "RE:")
        has_property_address_label = any("Property Address:" in line for line in gen_lines)
        re_as_second_label = False
        in_re_table = False
        for line in gen_lines:
            if "RE: Loan No." in line:
                in_re_table = True
            elif in_re_table and "RE:" in line and "Property Address:" not in line and "RE: Loan No." not in line:
                re_as_second_label = True
                break
            elif "</table>" in line:
                in_re_table = False
        
        if not has_property_address_label:
            issues.append("FAIL: Missing 'Property Address:' label — uses 'RE:' instead")
        elif re_as_second_label:
            issues.append("FAIL: Second RE row uses 'RE:' instead of 'Property Address:'")
        else:
            print("  PASS: Property Address label is correct")
        
        # Check 2: M583 should NOT be in Compress
        if "M583" in generated:
            issues.append("FAIL: M583 found in output — should NOT be present (source has only M567+M568)")
        else:
            print("  PASS: No M583 in Compress (correct)")
        
        # Check 3: Bullet margin-left
        if "margin-left:" in generated and ("30px" in generated or "35px" in generated):
            print("  PASS: Bullet table has margin-left")
        else:
            issues.append("FAIL: Bullet table missing margin-left")
        
        # Check 4: No extra <br> after Sincerely
        sincerely_idx = None
        for i, line in enumerate(gen_lines):
            if "Sincerely," in line:
                sincerely_idx = i
                break
        if sincerely_idx is not None:
            next_lines = [l.strip() for l in gen_lines[sincerely_idx+1:sincerely_idx+3] if l.strip()]
            if next_lines and next_lines[0] == "<br>":
                issues.append("FAIL: Extra <br> after Sincerely,")
            else:
                print("  PASS: No extra <br> after Sincerely")
        
        # Check 5: Compress should have only 2 parts (M567|M568)
        compress_match = re.search(r'Compress\(([^)]+)\)', generated)
        if compress_match:
            compress_content = compress_match.group(1)
            parts = compress_content.split("|")
            # Filter out non-address parts (skip translation Compress blocks)
            if "M567" in compress_content:
                part_count = len([p for p in parts if p.strip()])
                if part_count == 2:
                    print(f"  PASS: Compress has 2 parts (correct for LM300)")
                else:
                    issues.append(f"FAIL: Compress has {part_count} parts, expected 2")
    
    elif name == "IA004":
        # Check: M583 SHOULD be in Compress for IA004
        if "M583" in generated:
            print("  PASS: M583 present in Compress (correct for IA004)")
        else:
            issues.append("FAIL: M583 missing from Compress — IA004 should have 3-part")
        
        # Check: RE table should use colspan=2 for loan number row
        if 'colspan="2"' in generated:
            print("  PASS: colspan=2 for loan number row")
        else:
            issues.append("FAIL: Missing colspan=2 for loan number row")
        
        # Check: Bordered comparison table should exist
        if 'border: 1px solid' in generated or 'border:1px solid' in generated:
            print("  PASS: Bordered comparison table present")
        else:
            issues.append("FAIL: Missing bordered comparison table")
    
    elif name == "CL008":
        # Check: 3-column RE table
        if 'width="3%"' in generated:
            print("  PASS: 3-column RE table detected")
        else:
            issues.append("FAIL: Missing 3-column RE table (width=3%)")
        
        # Check: M583 SHOULD be in Compress for CL008
        if "M583" in generated:
            print("  PASS: M583 present in Compress (correct for CL008)")
        else:
            issues.append("FAIL: M583 missing from Compress — CL008 should have 3-part")
        
        # Check: Bullet lists with margin-left
        if "margin-left:" in generated:
            print("  PASS: Bullet lists have margin-left")
        else:
            issues.append("FAIL: Bullet lists missing margin-left")
        
        # Check: Numbered list items (1. and 2.)
        if 'valign="top">1.</td>' in generated or "valign=\"top\">1.</td>" in generated:
            print("  PASS: Numbered list items present")
        else:
            issues.append("FAIL: Numbered list items missing")
    
    if issues:
        print(f"\n  {'='*40}")
        print(f"  {name} ISSUES ({len(issues)}):")
        for issue in issues:
            print(f"    {issue}")
        return False
    else:
        print(f"\n  {name}: ALL CHECKS PASSED!")
        return True


if __name__ == "__main__":
    results = {}
    for tc in TEST_CASES:
        result = run_test(tc)
        results[tc["name"]] = result
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, passed in results.items():
        status = "PASS" if passed else ("SKIP" if passed is None else "FAIL")
        print(f"  {name}: {status}")
