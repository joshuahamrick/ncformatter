import sys, re
sys.path.insert(0, '.')

# Inline the normalize_html function to test it
exec(open('api/generate-template.py', encoding='utf-8').read().split('def load_system_prompt')[0])

tests = [
    # Bug 1: <> operator encoding
    ("{If('{[M583]}' <> '')}, {[M583]}{End If}",
     "{If('{[M583]}' &lt;&gt; '')}, {[M583]}{End If}",
     "Bug1: <> encoded"),
    # Bug 3: ServicingName prefix
    ("{[ServicingName]}",
     "{[plsMatrix.ServicingName]}",
     "Bug3: ServicingName prefix"),
    # Should NOT double-encode already correct
    ("{If('{[M583]}' &lt;&gt; '')}",
     "{If('{[M583]}' &lt;&gt; '')}",
     "No double-encode"),
]

all_pass = True
for inp, expected, label in tests:
    result = normalize_html(inp)
    ok = expected in result
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    print(f"  {status}: {label}")
    if not ok:
        print(f"    expected: {repr(expected)}")
        print(f"    got:      {repr(result)}")

print()
print("All tests passed!" if all_pass else "SOME TESTS FAILED")
