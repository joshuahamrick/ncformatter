#!/usr/bin/env python3
"""Convert ALL bullet points to tables in SI002"""

import re
from pathlib import Path

html_path = Path(__file__).parent.parent / "formatter examples" / "SI002" / "SI002-formatted.html"

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
i = 0

while i < len(lines):
    line = lines[i].strip()
    
    # Check if this line ends with " or</div>"
    if line.endswith(' or</div>'):
        # Collect consecutive items (ending with "or" or not)
        list_items = []
        j = i
        
        # First, collect all items ending with "or"
        while j < len(lines):
            current_line = lines[j].strip()
            if current_line.endswith(' or</div>'):
                match = re.match(r'<div>(.+?)\s+or</div>', current_line)
                if match:
                    list_items.append(match.group(1).strip())
                j += 1
                # Skip <br>
                if j < len(lines) and lines[j].strip() == '<br>':
                    j += 1
            else:
                break
        
        # Now check if there's a non-"or" item immediately after (part of same list)
        if j < len(lines):
            next_line = lines[j].strip()
            # If next line is a simple div (not a method header, not conditional), include it
            if next_line.startswith('<div>') and not next_line.startswith('<div>Method of Transfer:') and not next_line.startswith('<div>If ') and not next_line.startswith('<div>Primary Method') and not next_line.startswith('<div>To prove') and '{If' not in next_line and '{End If}' not in next_line:
                # Extract text
                match = re.match(r'<div>(.+?)</div>', next_line)
                if match:
                    text = match.group(1).strip()
                    # Don't include if it's too long (likely a paragraph, not a list item)
                    if len(text) < 150:
                        list_items.append(text)
                        j += 1
                        # Skip <br>
                        if j < len(lines) and lines[j].strip() == '<br>':
                            j += 1
        
        if len(list_items) >= 2:
            # Convert to table
            new_lines.append('<div><table width="100%" style="border-collapse: collapse"><tbody>')
            for item in list_items:
                new_lines.append('<tr>')
                new_lines.append('  <td width="3%" valign="top" style="text-align: center">•</td>')
                new_lines.append(f'  <td>{item}</td>')
                new_lines.append('</tr>')
            new_lines.append('</tbody></table></div>')
            new_lines.append('<br>')
            i = j
            continue
    
    new_lines.append(lines[i])
    i += 1

# Write back
with open(html_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Converted bullet points. File now has {len(new_lines)} lines")

