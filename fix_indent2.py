"""Fix two remaining indentation bugs around the para_counter / elif table section."""

src = open('api/generate-template.py', encoding='utf-8').read()
lines = src.split('\n')

# Find the para_counter += 1 line that's at indent=2 (should be indent=3)
# AND the "elif block.get('type') == 'table':" at indent=1 (should be indent=2)
fixed = False
for i, l in enumerate(lines):
    if l == '\t\tpara_counter += 1':
        # Check if next substantive line after seen_salutation block is 'elif' at indent=1
        # Look for the sequence: para_counter, formatted.append, maybe seen_salutation, then elif
        # We need to add one tab to lines from para_counter down to (but not including) elif
        print(f"Found para_counter at line {i+1}")
        
        # Find the end of this block (the 'elif' at indent=1 or 2)
        j = i
        while j < len(lines):
            stripped = lines[j].lstrip('\t')
            indent = len(lines[j]) - len(stripped)
            if indent <= 1 and stripped.startswith('elif') and not fixed:
                # Add one tab to lines i through j-1
                print(f"Found elif at line {j+1}, fixing lines {i+1}-{j}")
                for k in range(i, j):
                    if lines[k]:  # Skip blank lines
                        lines[k] = '\t' + lines[k]
                # Also fix the elif itself (should be at indent=2)
                if lines[j].startswith('\telif'):
                    lines[j] = '\t' + lines[j]
                    print(f"  Fixed elif: {repr(lines[j][:60])}")
                fixed = True
                break
            j += 1
        break

if not fixed:
    print("ERROR: Could not find the pattern to fix")
    exit(1)

open('api/generate-template.py', 'w', encoding='utf-8').write('\n'.join(lines))
print("Done! Verifying...")

# Verify
src2 = open('api/generate-template.py', encoding='utf-8').read()
lines2 = src2.split('\n')
for i, l in enumerate(lines2):
    if 'para_counter += 1' in l and 'seen_salutation' not in l:
        indent = len(l) - len(l.lstrip('\t'))
        if indent == 3:
            print(f"  para_counter is now at indent=3 (line {i+1}): OK")
    if "elif block.get('type') == 'table':" in l:
        indent = len(l) - len(l.lstrip('\t'))
        print(f"  elif is now at indent={indent} (line {i+1}): {'OK' if indent==2 else 'STILL WRONG'}")
