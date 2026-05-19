"""
Fix the indentation bug in format_ir_for_prompt.

The empty-check block (if not text or len(text) < 3:) was accidentally placed at
indent=2 (outside `if block.get('type') == 'paragraph':`) after the last StrReplace.
It should be at indent=3 (inside the paragraph type check).

This script:
1. Finds the `\t\t# Handle empty paragraphs` line at indent=2
2. Adds one extra tab to that comment and the `if not text` line
3. Adds one extra tab to everything inside the empty check (up to and including `\t\t\tcontinue`)
4. Leaves the non-empty code at indent=3 (now correctly OUTSIDE the empty check)
"""

src = open('api/generate-template.py', encoding='utf-8').read()
lines = src.split('\n')

# Find the offending section: `\t\t# Handle empty paragraphs`
start_line = None
for i, l in enumerate(lines):
    if l == '\t\t# Handle empty paragraphs':
        start_line = i
        break

if start_line is None:
    print("ERROR: could not find marker line")
    exit(1)

# Find the `\t\t\tcontinue` that ends the empty block (currently at indent=3)
end_line = None
for i in range(start_line, min(start_line + 100, len(lines))):
    if lines[i] == '\t\t\tcontinue':
        end_line = i
        break

if end_line is None:
    print("ERROR: could not find continue line")
    exit(1)

print(f"Fixing lines {start_line+1} to {end_line+1}")
print(f"  Before: {repr(lines[start_line])}")
print(f"  Continue at: {repr(lines[end_line])}")

# Add one tab to lines from start_line through end_line (inclusive)
for i in range(start_line, end_line + 1):
    lines[i] = '\t' + lines[i]

print(f"  After: {repr(lines[start_line])}")
print(f"  Continue after fix: {repr(lines[end_line])}")

# Write back
open('api/generate-template.py', 'w', encoding='utf-8').write('\n'.join(lines))
print("Done!")
