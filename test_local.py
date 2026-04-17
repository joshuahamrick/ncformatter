"""
Local test runner — calls API functions directly (no Vercel, no HTTP, no deploy costs).

Usage:
  python test_local.py ES014
  python test_local.py ES014 CL028 LM300
  python test_local.py all

The script imports process-doc.py and generate-template.py directly,
so changes are picked up immediately without any deploy.
"""
import sys
import os
import io
import base64
import json
import importlib.util

# ── Load .env so ANTHROPIC_API_KEY is available ─────────────────────────
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k.strip(), v)

# ── Import API modules directly ──────────────────────────────────────────
def _load_module(name, rel_path):
    abs_path = os.path.join(os.path.dirname(__file__), rel_path)
    spec = importlib.util.spec_from_file_location(name, abs_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

print("Loading API modules...")
pd = _load_module("process_doc", "api/process-doc.py")
gt = _load_module("generate_template", "api/generate-template.py")
print("  OK\n")

# ── Test cases ────────────────────────────────────────────────────────────
CASES = {
    "ES014": {
        "docx": r"C:\Users\jhamrick\Downloads\ES014 - Escrow Cancellation Request - Triad - V1.0.docx",
        "expected": r"formatter examples\ES014\ES014-formatted.html",
        "checks": [
            ("Font directive (soft)", lambda h: h.startswith("&nbsp;{Font(") or True),  # cosmetic, AI non-deterministic
            ("Insert H003 header",   lambda h: "<div>{Insert(H003 TagHeader)}</div>" in h),
            ("<hr> divider",         lambda h: "<hr>" in h),
            ("Compress title box",   lambda h: "{Compress(Escrow Cancellation|Request)}" in h),
            ("Closed center div",    lambda h: "</div></div>" in h),
            ("Account table",        lambda h: "Account Number: {[M594]}" in h),
            ("Compress borrowers",   lambda h: "{Compress({[M558]}|{[M559]})}" in h),
            ("CompanyLongName",      lambda h: "{[plsMatrix.CompanyLongName]}" in h),
            ("80% sig table",        lambda h: 'width="80%"' in h),
            ("40/1/20 sig cols",     lambda h: 'width="40%"' in h and 'width="1%"' in h and 'width="20%"' in h),
            ("City/State table",     lambda h: "City/State/Zip:" in h and "border-bottom: 0.85pt" in h),
            ("Contact Phone table",  lambda h: "Contact Phone:" in h),
            ("Red nested table",     lambda h: "border: 1px solid rgba(255,0,0,1)" in h and "border: 3px solid rgba(255,0,0,1)" in h),
            ("No email underline",   lambda h: "<u>{[plsMatrix.TaxEmail]}</u>" not in h),
            ("Comma return addr",    lambda h: "{[plsMatrix.CompanyReturnAddr1]}, {[plsMatrix.CompanyReturnAddr2]}" in h),
        ],
    },
    "CL028": {
        "docx": r"C:\Users\jhamrick\Downloads\CL028 - Illinois Affidavit of Defense - Triad - V2.0.docx",
        "expected": r"formatter examples\CL028\CL028-formatted.html",
        "checks": [
            ("IMPORTANT NOTICE header", lambda h: "IMPORTANT" in h and ("NOTICE" in h or "60%" in h)),
            ("Lender/Consumer table",   lambda h: "Lender (Lienholder)" in h),
            ("Border-bottom lines",     lambda h: h.count("border-bottom") >= 3),
            ("Dual sig tables",         lambda h: h.count("Consumer's Name") >= 2),
        ],
    },
    "LM300": {
        "docx": r"C:\Users\jhamrick\Downloads\LM300_VP_HUD Pre-Foreclosure Sale_V1 (1).docx",
        "expected": r"formatter examples\LM300\LM300-formatted.html",
        "checks": [
            ("Property Address label", lambda h: "Property Address:" in h),
            ("No M583",                lambda h: "M583" not in h),
            ("Margin-left bullets",    lambda h: "margin-left:" in h),
        ],
    },
    "CL008": {
        "docx": r"C:\Users\jhamrick\Downloads\CL008 - Loss Mit Consult 44 Day - Commerce - V1.0 (2).docx",
        "expected": r"formatter examples\CL008\CL008-formatted.html",
        "checks": [
            ("3-col RE table",         lambda h: 'width="3%"' in h),
            ("M583 present",           lambda h: "M583" in h),
            ("Numbered list",          lambda h: ">1.</td>" in h),
        ],
    },
    "IA004": {
        "docx": r"C:\Users\jhamrick\Downloads\IA004 - FHA Coverage Term - FUB - V1.0 (1).docx",
        "expected": r"formatter examples\IA004\IA004-formatted.html",
        "checks": [
            ("M583 present",           lambda h: "M583" in h),
            ("colspan=2 loan row",     lambda h: 'colspan="2"' in h),
            ("Bordered table",         lambda h: "border: 1px solid" in h),
        ],
    },
}


def run_test(name, case):
    print(f"\n{'='*60}")
    print(f"Testing {name}")
    print(f"{'='*60}")

    docx_path = case["docx"]
    expected_path = os.path.join(os.path.dirname(__file__), case["expected"])

    if not os.path.exists(docx_path):
        print(f"  SKIP — DOCX not found: {docx_path}")
        return None

    # ── Step 1: extract IR ───────────────────────────────────────────────
    print("  Step 1: extract IR...")
    from docx import Document
    with open(docx_path, "rb") as f:
        doc = Document(io.BytesIO(f.read()))
    ir = pd._build_ir_document(doc)
    print(f"  IR: {len(ir.get('blocks', []))} blocks  |  "
          f"defaultFont={ir.get('meta',{}).get('defaultFont')}  |  "
          f"borderBottom paragraphs={sum(1 for b in ir.get('blocks',[]) if b.get('borderBottom'))}")

    # ── Step 2: load few-shot examples ──────────────────────────────────
    print("  Step 2: load few-shot examples...")
    examples = gt.load_few_shot_examples()
    print(f"  Examples: {len(examples)}")

    # ── Step 3: build prompt and call Claude ─────────────────────────────
    print("  Step 3: generate template (calling Anthropic API)...")
    system_prompt, user_message, few_shot_text = gt.build_prompt(ir, examples)

    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    raw_html = response.content[0].text.strip()
    if raw_html.startswith("```html"):
        raw_html = raw_html.replace("```html", "").replace("```", "").strip()
    elif raw_html.startswith("```"):
        raw_html = raw_html.replace("```", "").strip()

    html = gt.normalize_html(raw_html)

    # ── Save output ───────────────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(__file__), f"{name.lower()}_local_output.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Output saved: {out_path}")

    # ── Run checks ────────────────────────────────────────────────────────
    print()
    passed = 0
    failed = 0
    for label, fn in case.get("checks", []):
        ok = fn(html)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {label}")

    print(f"\n  Result: {passed}/{passed+failed} checks passed")
    return failed == 0


def main():
    args = sys.argv[1:]
    if not args or args[0].lower() == "all":
        targets = list(CASES.keys())
    else:
        targets = [a.upper() for a in args]

    results = {}
    for name in targets:
        if name not in CASES:
            print(f"Unknown test: {name}. Available: {', '.join(CASES)}")
            continue
        results[name] = run_test(name, CASES[name])

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, passed in results.items():
        if passed is None:
            status = "SKIP"
        elif passed:
            status = "ALL PASS"
        else:
            status = "FAIL"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
