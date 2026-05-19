"""Fix the final indentation issue: para_counter at indent=2, elif at indent=1.
Both should be one tab higher."""

src = open('api/generate-template.py', encoding='utf-8').read()
lines = src.split('\n')

# Find the para_counter += 1 at indent=2
for i, l in enumerate(lines):
    if l == '\t\tpara_counter += 1':
        print(f"Found target at line {i+1}")
        # Look forward to find the 'elif' at indent=1
        for j in range(i, min(i+20, len(lines))):
            stripped = lines[j].lstrip('\t')
            indent = len(lines[j]) - len(stripped)
            if indent <= 1 and stripped.startswith('elif'):
                # Add one tab to lines i..j (inclusive)
                for k in range(i, j+1):
                    if lines[k]:
                        lines[k] = '\t' + lines[k]
                print(f"Fixed lines {i+1}-{j+1}")
                break
        break

open('api/generate-template.py', 'w', encoding='utf-8').write('\n'.join(lines))
print("Done!")

# Verify syntax
import subprocess
result = subprocess.run(['python', '-m', 'py_compile', 'api/generate-template.py'],
                       capture_output=True, text=True)
if result.returncode == 0:
    print("Syntax OK!")
else:
    print("SYNTAX ERROR:", result.stderr)
